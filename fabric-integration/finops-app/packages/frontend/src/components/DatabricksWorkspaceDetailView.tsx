"use client";

import React, { useState } from "react";
import {
  DatabricksConnection,
  DatabricksWorkspaceDiscovery,
  CategoryDiscoveryStatus,
} from "@/types";
import {
  ArrowLeft,
  RefreshCw,
  Server,
  Layers,
  Database,
  Cpu,
  Workflow,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  FolderTree,
  ExternalLink,
  Clock,
  User,
} from "lucide-react";

interface DatabricksWorkspaceDetailViewProps {
  connection: DatabricksConnection;
  discovery: DatabricksWorkspaceDiscovery | null;
  isLoading: boolean;
  onBack: () => void;
  onRefresh: () => void;
}

type DetailTab =
  | "overview"
  | "clusters"
  | "warehouses"
  | "jobs"
  | "pipelines"
  | "model_serving"
  | "unity_catalog"
  | "apps"
  | "history";

export const DatabricksWorkspaceDetailView: React.FC<DatabricksWorkspaceDetailViewProps> = ({
  connection,
  discovery,
  isLoading,
  onBack,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");

  const categories = discovery?.categories || {};
  const resources = discovery?.resources || [];

  const clusters = resources.filter((r) => r.resource_type === "cluster");
  const warehouses = resources.filter((r) => r.resource_type === "warehouse");
  const jobs = resources.filter((r) => r.resource_type === "job");
  const pipelines = resources.filter((r) => r.resource_type === "pipeline");
  const servingEndpoints = resources.filter((r) => r.resource_type === "serving_endpoint");
  const catalogs = resources.filter((r) => r.resource_type === "catalog");
  const apps = resources.filter((r) => r.resource_type === "app");

  const getCategoryStatusBadge = (status?: CategoryDiscoveryStatus) => {
    switch (status) {
      case "available":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Available
          </span>
        );
      case "permission_denied":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <ShieldAlert className="w-3 h-3 text-rose-600" />
            Permission Denied
          </span>
        );
      case "no_resources_found":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-50 text-slate-600 border border-slate-200">
            Empty (0 Found)
          </span>
        );
      case "unsupported":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Unsupported
          </span>
        );
      case "connection_error":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="w-3 h-3 text-rose-600" />
            Connection Error
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500">
            Not Discovered
          </span>
        );
    }
  };

  const renderCategoryBanner = (catName: string) => {
    const cat = categories[catName];
    if (!cat) return null;

    if (cat.status === "permission_denied") {
      return (
        <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-2.5 text-xs text-rose-800">
          <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Permission Denied:</span> The caller lacks authorized
            privileges to query this category in the target workspace.
            {cat.error_message && <p className="mt-1 text-[11px] font-mono">{cat.error_message}</p>}
          </div>
        </div>
      );
    }

    if (cat.status === "connection_error") {
      return (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2.5 text-xs text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Query Limitation:</span> Could not connect or query this
            category.
            {cat.error_message && <p className="mt-1 text-[11px] font-mono">{cat.error_message}</p>}
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-navy-900 transition"
              title="Back to all workspaces"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-navy-900">{connection.workspace_name}</h1>
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 uppercase">
                  {connection.cloud}
                </span>
                <span className="text-xs text-slate-500 font-mono">ID: {connection.workspace_id}</span>
              </div>
              <a
                href={connection.workspace_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 mt-0.5 font-mono"
              >
                {connection.workspace_url}
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition shadow-sm"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              Refresh Discovery
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-slate-200 mt-6 overflow-x-auto text-xs font-medium">
          {[
            { id: "overview", label: "Overview", icon: Layers, count: null },
            { id: "clusters", label: "Compute Clusters", icon: Cpu, count: clusters.length },
            { id: "warehouses", label: "SQL Warehouses", icon: Database, count: warehouses.length },
            { id: "jobs", label: "Jobs & Workflows", icon: Workflow, count: jobs.length },
            { id: "pipelines", label: "Pipelines", icon: FolderTree, count: pipelines.length },
            { id: "model_serving", label: "Model Serving", icon: Sparkles, count: servingEndpoints.length },
            { id: "unity_catalog", label: "Unity Catalog", icon: Database, count: catalogs.length },
            { id: "apps", label: "Databricks Apps", icon: Server, count: apps.length },
            { id: "history", label: "Discovery History", icon: Clock, count: null },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as DetailTab)}
                className={`flex items-center gap-1.5 px-3.5 py-2.5 border-b-2 font-medium whitespace-nowrap transition ${
                  isActive
                    ? "border-indigo-600 text-indigo-700 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? "text-indigo-600" : "text-slate-400"}`} />
                {tab.label}
                {tab.count !== null && (
                  <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600">
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Contents */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Quick Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
              <span className="text-xs text-slate-500 font-medium">Compute Clusters</span>
              <div className="text-2xl font-bold text-navy-900 mt-1">{clusters.length}</div>
              <div className="mt-1">{getCategoryStatusBadge(categories.clusters?.status)}</div>
            </div>
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
              <span className="text-xs text-slate-500 font-medium">SQL Warehouses</span>
              <div className="text-2xl font-bold text-navy-900 mt-1">{warehouses.length}</div>
              <div className="mt-1">{getCategoryStatusBadge(categories.warehouses?.status)}</div>
            </div>
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
              <span className="text-xs text-slate-500 font-medium">Model Serving Endpoints</span>
              <div className="text-2xl font-bold text-navy-900 mt-1">{servingEndpoints.length}</div>
              <div className="mt-1">{getCategoryStatusBadge(categories.model_serving?.status)}</div>
            </div>
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
              <span className="text-xs text-slate-500 font-medium">Databricks Apps</span>
              <div className="text-2xl font-bold text-navy-900 mt-1">{apps.length}</div>
              <div className="mt-1">{getCategoryStatusBadge(categories.apps?.status)}</div>
            </div>
          </div>

          {/* Capabilities and Category Breakdown */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-bold text-navy-900 mb-3">Discovery Category Breakdown</h3>
            <div className="divide-y divide-slate-100 text-xs">
              {Object.entries(categories).map(([catKey, catVal]) => (
                <div key={catKey} className="py-2.5 flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-slate-800 capitalize">{catKey.replace("_", " ")}</span>
                    {catVal.error_message && (
                      <p className="text-[11px] text-slate-400 mt-0.5">{catVal.error_message}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-slate-600 font-medium">{catVal.resource_count} items</span>
                    {getCategoryStatusBadge(catVal.status)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Compute Clusters Tab */}
      {activeTab === "clusters" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("clusters")}
          {clusters.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No compute clusters discovered in this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">Cluster Name</th>
                    <th className="pb-2">ID</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Runtime</th>
                    <th className="pb-2">Node Type</th>
                    <th className="pb-2">Workers</th>
                    <th className="pb-2">Creator</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {clusters.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{c.name}</td>
                      <td className="py-2.5 font-mono text-[11px] text-slate-500">{c.id}</td>
                      <td className="py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            c.status === "RUNNING"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-slate-600 font-mono text-[11px]">
                        {c.metadata.spark_version || "-"}
                      </td>
                      <td className="py-2.5 text-slate-600 font-mono text-[11px]">
                        {c.metadata.node_type_id || "-"}
                      </td>
                      <td className="py-2.5 text-slate-600">{c.metadata.num_workers ?? "Auto"}</td>
                      <td className="py-2.5 text-slate-500 flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {c.creator || "System"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* SQL Warehouses Tab */}
      {activeTab === "warehouses" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("warehouses")}
          {warehouses.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No SQL warehouses discovered in this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">Warehouse Name</th>
                    <th className="pb-2">ID</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Size</th>
                    <th className="pb-2">Auto-Stop</th>
                    <th className="pb-2">Creator</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {warehouses.map((w) => (
                    <tr key={w.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{w.name}</td>
                      <td className="py-2.5 font-mono text-[11px] text-slate-500">{w.id}</td>
                      <td className="py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            w.status === "RUNNING"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {w.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-slate-600 font-semibold">{w.metadata.cluster_size || "-"}</td>
                      <td className="py-2.5 text-slate-600">{w.metadata.auto_stop_mins ? `${w.metadata.auto_stop_mins} mins` : "Disabled"}</td>
                      <td className="py-2.5 text-slate-500">{w.creator || "System"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Jobs Tab */}
      {activeTab === "jobs" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("jobs")}
          {jobs.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No jobs or workflows discovered in this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">Job Name</th>
                    <th className="pb-2">ID</th>
                    <th className="pb-2">Trigger</th>
                    <th className="pb-2">Tasks Count</th>
                    <th className="pb-2">Creator</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {jobs.map((j) => (
                    <tr key={j.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{j.name}</td>
                      <td className="py-2.5 font-mono text-[11px] text-slate-500">{j.id}</td>
                      <td className="py-2.5">{j.status}</td>
                      <td className="py-2.5 font-semibold text-slate-700">{j.metadata.tasks_count}</td>
                      <td className="py-2.5 text-slate-500">{j.creator || "System"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Model Serving Tab */}
      {activeTab === "model_serving" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("model_serving")}
          {servingEndpoints.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No model serving endpoints discovered in this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">Endpoint Name</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Creator</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {servingEndpoints.map((ep) => (
                    <tr key={ep.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{ep.name}</td>
                      <td className="py-2.5">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {ep.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-slate-500">{ep.creator || "System"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Unity Catalog Tab */}
      {activeTab === "unity_catalog" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("unity_catalog")}
          {catalogs.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No catalogs discovered or permission denied.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">Catalog Name</th>
                    <th className="pb-2">Owner</th>
                    <th className="pb-2">Comment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {catalogs.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{c.name}</td>
                      <td className="py-2.5 text-slate-600">{c.creator || "-"}</td>
                      <td className="py-2.5 text-slate-500">{c.metadata.comment || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Apps Tab */}
      {activeTab === "apps" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          {renderCategoryBanner("apps")}
          {apps.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-xs">
              No Databricks Apps discovered in this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-medium">
                    <th className="pb-2">App Name</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Creator</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {apps.map((a) => (
                    <tr key={a.id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-semibold text-slate-900">{a.name}</td>
                      <td className="py-2.5">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {a.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-slate-500">{a.creator || "System"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* History Tab */}
      {activeTab === "history" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm text-xs">
          <h3 className="text-sm font-bold text-navy-900 mb-3">Discovery Execution Telemetry</h3>
          {discovery ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <span className="text-slate-500 font-medium">Last Discovery Timestamp:</span>
                <span className="font-mono text-slate-800">{new Date(discovery.discovered_at).toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <span className="text-slate-500 font-medium">Overall Execution Outcome:</span>
                <span className="font-semibold uppercase text-emerald-700">{discovery.overall_status}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <span className="text-slate-500 font-medium">Total Discovered Resources:</span>
                <span className="font-bold text-slate-900">{discovery.total_resources_count}</span>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400">No discovery telemetry recorded yet.</div>
          )}
        </div>
      )}
    </div>
  );
};

