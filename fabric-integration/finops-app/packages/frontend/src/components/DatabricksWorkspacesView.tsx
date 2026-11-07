"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  DatabricksConnection,
  DatabricksWorkspaceDiscovery,
  DatabricksConnectionTestResponse,
} from "@/types";
import {
  listDatabricksConnections,
  testDatabricksConnection,
  getWorkspaceDiscovery,
  refreshWorkspaceDiscovery,
} from "@/lib/api";
import { DatabricksWorkspaceDetailView } from "./DatabricksWorkspaceDetailView";
import {
  Server,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Database,
  ArrowRight,
  Layers,
  Sparkles,
} from "lucide-react";

interface DatabricksWorkspacesViewProps {
  selectedWorkspaceId?: string; // "all" or specific connection_id
  onWorkspaceChange?: (workspaceId: string) => void;
}

export const DatabricksWorkspacesView: React.FC<DatabricksWorkspacesViewProps> = ({
  selectedWorkspaceId = "all",
  onWorkspaceChange,
}) => {
  const [connections, setConnections] = useState<DatabricksConnection[]>([]);
  const [activeDetailConnectionId, setActiveDetailConnectionId] = useState<string | null>(null);
  const [discoveryMap, setDiscoveryMap] = useState<Record<string, DatabricksWorkspaceDiscovery>>({});
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ connectionId: string; result: DatabricksConnectionTestResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch registered workspaces
  const fetchConnections = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const conns = await listDatabricksConnections();
      setConnections(conns);

      // Pre-fetch cached discovery for each connection
      for (const c of conns) {
        try {
          const disc = await getWorkspaceDiscovery(c.connection_id);
          setDiscoveryMap((prev) => ({ ...prev, [c.connection_id]: disc }));
        } catch {
          // Non-blocking
        }
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load Databricks connections.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // Test Connection Action
  const handleTestConnection = async (connectionId: string) => {
    setActionLoadingId(`test-${connectionId}`);
    setTestResult(null);
    try {
      const res = await testDatabricksConnection(connectionId);
      setTestResult({ connectionId, result: res });
      // Update local connection status
      setConnections((prev) =>
        prev.map((c) => (c.connection_id === connectionId ? { ...c, status: res.status } : c))
      );
    } catch (err: any) {
      alert(`Test connection failed: ${err?.message || "Unknown error"}`);
    } finally {
      setActionLoadingId(null);
    }
  };

  // Refresh Discovery Action
  const handleRefreshDiscovery = async (connectionId: string) => {
    setActionLoadingId(`refresh-${connectionId}`);
    try {
      const disc = await refreshWorkspaceDiscovery(connectionId);
      setDiscoveryMap((prev) => ({ ...prev, [connectionId]: disc }));
      // Also update connection
      const updatedConns = await listDatabricksConnections();
      setConnections(updatedConns);
    } catch (err: any) {
      alert(`Refresh discovery failed: ${err?.message || "Unknown error"}`);
    } finally {
      setActionLoadingId(null);
    }
  };

  // If viewing details of a specific workspace
  if (activeDetailConnectionId) {
    const activeConn = connections.find((c) => c.connection_id === activeDetailConnectionId);
    if (activeConn) {
      return (
        <DatabricksWorkspaceDetailView
          connection={activeConn}
          discovery={discoveryMap[activeConn.connection_id] || null}
          isLoading={actionLoadingId === `refresh-${activeConn.connection_id}`}
          onBack={() => setActiveDetailConnectionId(null)}
          onRefresh={() => handleRefreshDiscovery(activeConn.connection_id)}
        />
      );
    }
  }

  // Filter connections if a single workspace is selected via global filter
  const displayedConnections =
    selectedWorkspaceId === "all"
      ? connections
      : connections.filter((c) => c.connection_id === selectedWorkspaceId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-indigo-600" />
              <h2 className="text-lg font-bold text-navy-900">Databricks Workspaces</h2>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                Multi-Workspace Architecture
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Connect, discover, and monitor compute, warehouses, workflows, and Unity Catalog across
              Azure and AWS Databricks workspaces.
            </p>
          </div>

          <button
            onClick={fetchConnections}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 disabled:opacity-50 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh Workspaces
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Workspace Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {displayedConnections.map((conn) => {
          const disc = discoveryMap[conn.connection_id];
          const isTesting = actionLoadingId === `test-${conn.connection_id}`;
          const isRefreshing = actionLoadingId === `refresh-${conn.connection_id}`;
          const currentTest = testResult?.connectionId === conn.connection_id ? testResult.result : null;

          const clustersCount = disc?.categories?.clusters?.resource_count ?? 0;
          const warehousesCount = disc?.categories?.warehouses?.resource_count ?? 0;
          const totalAssets = disc?.total_resources_count ?? 0;

          return (
            <div
              key={conn.connection_id}
              className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:border-indigo-300 transition flex flex-col justify-between"
            >
              <div>
                {/* Top Card Bar */}
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200">
                        {conn.cloud}
                      </span>
                      <h3 className="text-base font-bold text-navy-900">{conn.workspace_name}</h3>
                    </div>
                    <span className="text-xs text-slate-400 font-mono mt-0.5 block">
                      ID: {conn.workspace_id}
                    </span>
                  </div>

                  {/* Status Pill */}
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                      conn.status === "connected"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : conn.status === "auth_failed"
                        ? "bg-amber-50 text-amber-700 border border-amber-200"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {conn.status === "connected" ? (
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="w-3 h-3 text-amber-600" />
                    )}
                    {conn.status}
                  </span>
                </div>

                {/* Host link */}
                <div className="mt-3">
                  <a
                    href={conn.workspace_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 font-mono truncate"
                  >
                    {conn.workspace_url}
                    <ExternalLink className="w-3 h-3 shrink-0" />
                  </a>
                </div>

                {/* Resource Stats Snapshot */}
                <div className="grid grid-cols-3 gap-2 mt-4 p-3 bg-slate-50 border border-slate-100 rounded-lg text-center">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-medium">Clusters</span>
                    <div className="text-sm font-bold text-navy-900">{clustersCount}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-medium">Warehouses</span>
                    <div className="text-sm font-bold text-navy-900">{warehousesCount}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-medium">Total Assets</span>
                    <div className="text-sm font-bold text-indigo-700">{totalAssets}</div>
                  </div>
                </div>

                {/* Test Result Callout if available */}
                {currentTest && (
                  <div
                    className={`mt-3 p-2.5 rounded-lg text-xs border ${
                      currentTest.success
                        ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                        : "bg-rose-50 text-rose-800 border-rose-200"
                    }`}
                  >
                    <span className="font-semibold">
                      {currentTest.success ? "Auth Verified:" : "Auth Failed:"}
                    </span>{" "}
                    {currentTest.details}
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="mt-5 pt-4 border-t border-slate-100 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleTestConnection(conn.connection_id)}
                    disabled={isTesting}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                  >
                    {isTesting ? "Testing..." : "Test Connection"}
                  </button>
                  <button
                    onClick={() => handleRefreshDiscovery(conn.connection_id)}
                    disabled={isRefreshing}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                  >
                    <RefreshCw className={`w-3 h-3 ${isRefreshing ? "animate-spin" : ""}`} />
                    Refresh
                  </button>
                </div>

                <button
                  onClick={() => setActiveDetailConnectionId(conn.connection_id)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition"
                >
                  View Details
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

